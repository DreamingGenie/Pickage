package com.ssafy.pickage.domain.community;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.*;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import com.ssafy.pickage.PickageApplication;
import com.ssafy.pickage.support.DisposableTestDatabase;
import com.ssafy.pickage.domain.community.payload.*;

class ApplicationContractReviewTest {
    static DisposableTestDatabase database;
    static ConfigurableApplicationContext context;
    static JdbcTemplate jdbc;
    static CommunitySnapshotRepository repository;
    static MockMvc mvc;
    @BeforeAll static void start() {
        database=DisposableTestDatabase.createFor("315");
        var ds=(DriverManagerDataSource)database.dataSource();
        try {
            context=new SpringApplicationBuilder(PickageApplication.class).run(
                "--server.port=0","--server.address=127.0.0.1",
                "--spring.datasource.url="+ds.getUrl(),"--spring.datasource.username="+ds.getUsername(),
                "--spring.datasource.password="+ds.getPassword());
            jdbc=context.getBean(JdbcTemplate.class);repository=context.getBean(CommunitySnapshotRepository.class);
            mvc=MockMvcBuilders.webAppContextSetup((WebApplicationContext)context).build();
        } catch(RuntimeException e) { database.close();database=null;throw e; }
    }
    @AfterAll static void stop() { if(context!=null)context.close();if(database!=null)database.close(); }
    @BeforeEach void seed() {
        jdbc.update("DELETE FROM package");
        jdbc.update("INSERT INTO package(package_id,name) VALUES (7,'fixture')");
    }
    static CommunitySnapshotRow row() {
        return new CommunitySnapshotRow(7,UUID.randomUUID(),(short)1,Instant.now(),DataStatus.NO_DISCUSSION_DATA,
            new CommunityResultPayload(new RepositoryPayload("fixture/repo","PACKAGE_SCOPED"),1,180,null,List.of(),List.of()));
    }
    @Test void R08_realApplicationInitialWire() throws Exception {
        var response=mvc.perform(get("/api/packages/community").param("name","fixture")).andReturn().getResponse();
        System.out.println("INITIAL_WIRE="+response.getContentAsString());
        mvc.perform(get("/api/packages/community").param("name","fixture"))
            .andExpect(status().isOk()).andExpect(jsonPath("$.data.view_status").value("IDLE"));
    }
    @Test void R08_blankNameMustBeV001() throws Exception {
        mvc.perform(get("/api/packages/community").param("name",""))
            .andExpect(status().isBadRequest()).andExpect(jsonPath("$.code").value("V001"));
    }
    @Test void R08_malformedNameMustBeV004() throws Exception {
        mvc.perform(get("/api/packages/community").param("name","bad/name"))
            .andExpect(status().isBadRequest()).andExpect(jsonPath("$.code").value("V004"));
    }
    @Test void R08_errorMustAlsoBeNoStore() throws Exception {
        mvc.perform(get("/api/packages/community"))
            .andExpect(status().isBadRequest()).andExpect(header().string("Cache-Control","no-store"));
    }
    @Test void R06_unsupportedPayloadMustBeIgnored() {
        repository.upsert(row());jdbc.update("UPDATE community_snapshot SET payload_version=99");
        assertTrue(repository.findByPackageId(7).isEmpty());
    }
    @Test void R06_unsupportedPolicyMustBeIgnored() {
        repository.upsert(row());jdbc.update("UPDATE community_snapshot SET result=jsonb_set(result,'{policy_version}','99')");
        assertTrue(repository.findByPackageId(7).isEmpty());
    }
    @Test void R06_invalidSupportedPayloadMustBeRejected() {
        repository.upsert(row());jdbc.update("UPDATE community_snapshot SET result='{}'::jsonb");
        assertThrows(CommunitySnapshotPayloadException.class,()->repository.findByPackageId(7));
    }
    @Test void R11_realTransactionRollbackKeepsPreviousRow() {
        var old=row();repository.upsert(old);
        var tx=new TransactionTemplate(context.getBean(PlatformTransactionManager.class));
        assertThrows(IllegalStateException.class,()->tx.executeWithoutResult(status->{repository.upsert(row());throw new IllegalStateException("synthetic rollback");}));
        assertEquals(old.snapshotId(),repository.findByPackageId(7).orElseThrow().snapshotId());
    }
    @Test void R12_existingPackageSearchStillWorks() throws Exception {
        mvc.perform(get("/api/packages/search").param("q","fixture"))
            .andExpect(status().isOk()).andExpect(jsonPath("$.success").value(true));
    }
    @Test void R14_existingSeedTruncateMustRemainExecutable() {
        assertDoesNotThrow(()->jdbc.execute("TRUNCATE similar_package, package_version_snapshot, package_snapshot, version, package"));
    }
    @Test void R12_actualRuntimeSnakeCaseAndNullKeys() throws Exception {
        repository.upsert(row());
        var response=mvc.perform(get("/api/packages/community").param("name","fixture")).andReturn().getResponse();
        System.out.println("RESULT_WIRE="+response.getContentAsString());
        var json=new com.fasterxml.jackson.databind.ObjectMapper().readTree(response.getContentAsString());
        assertAll(()->assertTrue(json.path("data").has("package_name")),
            ()->assertTrue(json.path("data").path("refresh").has("retry_at")));
    }
}
