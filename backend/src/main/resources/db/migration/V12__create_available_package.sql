-- 데이터가 존재하는 10만개 패키지만을 검색하기 위한 테이블 생성
CREATE TABLE available_package (
    package_id INTEGER PRIMARY KEY,
    package_name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT FK_AVAILABLE_PACKAGE_PACKAGE
        FOREIGN KEY (package_id)
        REFERENCES package(package_id)
        ON DELETE CASCADE
);