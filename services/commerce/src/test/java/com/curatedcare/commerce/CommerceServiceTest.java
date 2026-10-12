package com.curatedcare.commerce;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(properties={"spring.datasource.url=jdbc:h2:mem:zhifu_test;MODE=MySQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1"})
@Transactional
class CommerceServiceTest {
    @Autowired CommerceService service;
    @Autowired JdbcTemplate db;
    @Test void checkoutIsIdempotentAndOwnershipIsEnforced() {
        service.putCart(2,101,2);
        var a=service.checkout(2,"上海市世纪大道100号","checkout-one");
        var b=service.checkout(2,"上海市世纪大道100号","checkout-one");
        assertEquals(a.get("id"),b.get("id"));
        assertEquals(78,db.queryForObject("SELECT stock FROM products WHERE id=101",Integer.class));
        assertThrows(ResponseStatusException.class,()->service.order(3,a.get("id").toString()));
        assertThrows(ResponseStatusException.class,()->service.checkout(2,"北京市中关村大街100号","checkout-one"));
    }
    @Test void refundRequiresPaidOrderAndRestoresStockOnce() {
        service.putCart(2,101,1);
        String order=service.checkout(2,"上海市世纪大道100号","checkout-two").get("id").toString();
        assertThrows(ResponseStatusException.class,()->service.refund(2,order,"不喜欢","refund-two"));
        service.pay(2,order);
        var refund=service.refund(2,order,"不喜欢","refund-two");
        assertEquals(refund.get("id"),service.refund(2,order,"不喜欢","refund-another").get("id"));
        assertThrows(ResponseStatusException.class,()->service.ship(1,order));
        service.review(1,refund.get("id").toString(),true,"通过");
        service.review(1,refund.get("id").toString(),true,"重复审核");
        assertEquals("REFUNDED",service.order(2,order).get("status"));
        assertEquals(80,db.queryForObject("SELECT stock FROM products WHERE id=101",Integer.class));
    }
    @Test void cancelRestoresInventoryAndRejectsPayment() {
        service.putCart(2,102,3);
        String order=service.checkout(2,"上海市世纪大道100号","checkout-three").get("id").toString();
        service.cancel(2,order); service.cancel(2,order);
        assertEquals(100,db.queryForObject("SELECT stock FROM products WHERE id=102",Integer.class));
        assertThrows(ResponseStatusException.class,()->service.pay(2,order));
    }
    @Test void shippedOrdersCannotBeRefundedAutomatically() {
        service.putCart(2,103,1);
        String order=service.checkout(2,"上海市世纪大道100号","checkout-four").get("id").toString();
        service.pay(2,order);service.ship(1,order);
        assertThrows(ResponseStatusException.class,()->service.refund(2,order,"不喜欢","refund-four"));
    }
}
