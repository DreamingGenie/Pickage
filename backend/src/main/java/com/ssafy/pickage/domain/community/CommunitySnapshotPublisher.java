package com.ssafy.pickage.domain.community;

import com.ssafy.pickage.domain.community.refresh.RefreshTask;

import java.sql.*;
import java.time.*;
import java.util.concurrent.*;

/** 공유 pool의 connection 대기를 최대 두 작업으로 제한한다. 기한 후 얻은 connection도 즉시 반환한다. */
public final class CommunitySnapshotPublisher implements AutoCloseable {
    private final CommunitySnapshotRepository repository;
    private final ThreadPoolExecutor acquisitions =
            new ThreadPoolExecutor(0, 2, 30, TimeUnit.SECONDS, new SynchronousQueue<>());

    public CommunitySnapshotPublisher(CommunitySnapshotRepository repository) {
        this.repository = repository;
    }

    public void publish(CommunitySnapshotRow row, RefreshTask task) {
        task.requirePublishable();
        Duration budget =
                task.timeLeft().compareTo(CommunityProperties.PUBLISH_BUDGET) < 0
                        ? task.timeLeft()
                        : CommunityProperties.PUBLISH_BUDGET;
        Instant deadline = Instant.now().plus(budget);
        Lease lease = new Lease();
        try {
            acquisitions.execute(
                    () -> {
                        try {
                            lease.arrive(repository.dataSource().getConnection());
                        } catch (SQLException e) {
                            lease.fail();
                        }
                    });
            try (Connection c = lease.take(deadline)) {
                int oldNetwork = c.getNetworkTimeout();
                boolean oldAuto = c.getAutoCommit();
                boolean[] committed = {false};
                try {
                    c.setNetworkTimeout(Runnable::run, remaining(deadline));
                    c.setAutoCommit(false);
                    task.publishOwned(
                            () -> {
                                try {
                                    repository.write(c, row, task, deadline);
                                    task.requirePublishable();
                                    c.setNetworkTimeout(Runnable::run, remaining(deadline));
                                    c.commit();
                                    committed[0] = true;
                                } catch (SQLException e) {
                                    throw new IllegalStateException("Community publication failed");
                                }
                            });
                } finally {
                    // rollback 실패 시 autoCommit 복원으로 미확정 transaction을 commit하지 않는다.
                    if (!committed[0]) c.rollback();
                    if (!c.isClosed()) {
                        c.setAutoCommit(oldAuto);
                        c.setNetworkTimeout(Runnable::run, oldNetwork);
                    }
                }
            }
        } catch (SQLException | InterruptedException e) {
            if (e instanceof InterruptedException) Thread.currentThread().interrupt();
            throw new IllegalStateException("Community publication failed");
        } finally {
            lease.abandon();
        }
    }

    private static int remaining(Instant deadline) throws SQLException {
        long left = Duration.between(Instant.now(), deadline).toMillis();
        if (left <= 0) throw new SQLException("Publication deadline exceeded");
        return (int) Math.min(2000, left);
    }

    private static final class Lease {
        private Connection connection;
        private boolean abandoned, failed;

        synchronized void arrive(Connection c) throws SQLException {
            if (abandoned) c.close();
            else {
                connection = c;
                notifyAll();
            }
        }

        synchronized void fail() {
            failed = true;
            notifyAll();
        }

        synchronized Connection take(Instant deadline) throws SQLException, InterruptedException {
            while (connection == null && !failed) {
                wait(remaining(deadline));
            }
            if (failed) throw new SQLException("Connection unavailable");
            remaining(deadline);
            Connection result = connection;
            connection = null;
            abandoned = true;
            return result;
        }

        synchronized void abandon() {
            abandoned = true;
            if (connection != null) {
                try {
                    connection.close();
                } catch (SQLException ignored) {
                }
                connection = null;
            }
        }
    }

    public void close() {
        acquisitions.shutdownNow();
    }
}
