package com.curatedcare.commerce;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
public class SeedData implements ApplicationRunner {
    private final JdbcTemplate db; private final AuthService auth;
    @Value("${care.demo}") private boolean demo;
    @Value("${care.demo-password}") private String demoPassword;
    @Value("${care.admin-password}") private String adminPassword;
    @Value("${care.service-token}") private String serviceToken;
    public SeedData(JdbcTemplate db,AuthService auth) { this.db=db;this.auth=auth; }
    public void run(ApplicationArguments args) {
        if(!demo && (adminPassword.equals("Admin12345!") || serviceToken.equals("local-development-only"))) throw new IllegalStateException("非演示模式需要设置 ADMIN_PASSWORD 和 SERVICE_TOKEN");
        if(db.queryForObject("SELECT COUNT(*) FROM customers WHERE username='admin'",Integer.class)==0) db.update("INSERT INTO customers VALUES(?,?,?,?)",1,"admin",auth.hashPassword(adminPassword),"ADMIN");
        if(!demo) return;
        if(db.queryForObject("SELECT COUNT(*) FROM customers WHERE id=2",Integer.class)==0) {
            db.update("INSERT INTO customers VALUES(?,?,?,?)",2,"demo",auth.hashPassword(demoPassword),"CUSTOMER");
            db.update("INSERT INTO customers VALUES(?,?,?,?)",3,"other",auth.hashPassword(demoPassword),"CUSTOMER");
        }
        if(db.queryForObject("SELECT COUNT(*) FROM products",Integer.class)==0) {
            db.update("INSERT INTO products VALUES(?,?,?,?,?,?,?)",101,"静享降噪耳机","数码","蓝牙 5.3，主动降噪，续航 40 小时，支持一年质保。",299,80,true);
            db.update("INSERT INTO products VALUES(?,?,?,?,?,?,?)",102,"轻量通勤背包","生活","20L 容量，防泼水面料，独立电脑隔层。",159,100,true);
            db.update("INSERT INTO products VALUES(?,?,?,?,?,?,?)",103,"恒温随行杯","生活","316 不锈钢，450ml，保温约 6 小时。",89,120,true);
        }
    }
}
