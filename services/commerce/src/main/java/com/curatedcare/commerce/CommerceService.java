package com.curatedcare.commerce;

import java.math.BigDecimal;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import static com.curatedcare.commerce.AuthService.error;

@Service
public class CommerceService {
    private final JdbcTemplate db;
    public CommerceService(JdbcTemplate db) { this.db=db; }
    public List<Map<String,Object>> products() { return db.queryForList("SELECT * FROM products WHERE active=TRUE ORDER BY id"); }
    public List<Map<String,Object>> allProducts() { return db.queryForList("SELECT * FROM products ORDER BY id"); }
    public Map<String,Object> product(long id) {
        var rows=db.queryForList("SELECT * FROM products WHERE id=? AND active=TRUE",id);
        if(rows.isEmpty()) throw error(404,"商品不存在或已下架"); return rows.get(0);
    }
    public List<Map<String,Object>> cart(long user) { return db.queryForList("SELECT p.*,c.quantity FROM cart c JOIN products p ON c.product_id=p.id WHERE c.user_id=? ORDER BY p.id",user); }
    private void lockUser(long user) { db.queryForList("SELECT id FROM customers WHERE id=? FOR UPDATE",user); }
    @Transactional
    public void putCart(long user,long product,int quantity) {
        if(quantity<0 || quantity>99) throw error(400,"数量必须在 0 到 99 之间");
        lockUser(user); var p=product(product);
        if(quantity>((Number)p.get("stock")).intValue()) throw error(409,"库存不足");
        db.update("DELETE FROM cart WHERE user_id=? AND product_id=?",user,product);
        if(quantity>0) db.update("INSERT INTO cart VALUES(?,?,?)",user,product,quantity);
    }
    public List<Map<String,Object>> orders(long user) { return db.queryForList("SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC",user).stream().map(this::enrich).toList(); }
    public Map<String,Object> order(long user,String id) {
        var rows=db.queryForList("SELECT * FROM orders WHERE id=? AND user_id=?",id,user);
        if(rows.isEmpty()) throw error(404,"订单不存在");return enrich(rows.get(0));
    }
    private Map<String,Object> enrich(Map<String,Object> row) {
        var result=new LinkedHashMap<String,Object>(row);
        result.remove("fingerprint"); result.remove("request_key");
        result.put("items",db.queryForList("SELECT product_id,title,price,quantity FROM order_items WHERE order_id=? ORDER BY product_id",row.get("id")));
        result.put("refunds",db.queryForList("SELECT * FROM refunds WHERE order_id=?",row.get("id")));
        result.put("status_desc",switch(row.get("status").toString()) {case "PENDING"->"待付款";case "PAID"->"待发货";case "SHIPPED"->"已发货";case "REFUNDED"->"已退款";case "CANCELLED"->"已取消";default->"未知";});
        return result;
    }
    @Transactional
    public Map<String,Object> checkout(long user,String address,String key) {
        checkKey(key); address=address.strip(); if(address.length()<5 || address.length()>300) throw error(400,"请填写完整收货地址");
        lockUser(user);
        var previous=db.queryForList("SELECT * FROM orders WHERE user_id=? AND request_key=?",user,key);
        if(!previous.isEmpty()) {
            if(!AuthService.digest(address).equals(previous.get(0).get("fingerprint"))) throw error(409,"同一请求标识不能用于不同订单");
            return enrich(previous.get(0));
        }
        var items=cart(user); if(items.isEmpty()) throw error(400,"购物车为空");
        BigDecimal total=BigDecimal.ZERO;
        for(var item:items) {
            long pid=((Number)item.get("id")).longValue();
            var p=db.queryForMap("SELECT * FROM products WHERE id=? FOR UPDATE",pid);
            int q=((Number)item.get("quantity")).intValue();
            if(!Boolean.TRUE.equals(p.get("active")) || ((Number)p.get("stock")).intValue()<q) throw error(409,"商品已下架或库存不足");
            total=total.add(((BigDecimal)p.get("price")).multiply(BigDecimal.valueOf(q)));
            item.put("price",p.get("price")); item.put("title",p.get("title"));
        }
        String id="ZF"+UUID.randomUUID().toString().replace("-","").substring(0,20).toUpperCase();
        db.update("INSERT INTO orders VALUES(?,?,?,?,?,?,?,?)",id,user,total,"PENDING",address,System.currentTimeMillis(),key,AuthService.digest(address));
        for(var p:items) {
            db.update("INSERT INTO order_items VALUES(?,?,?,?,?)",id,p.get("id"),p.get("title"),p.get("price"),p.get("quantity"));
            db.update("UPDATE products SET stock=stock-? WHERE id=?",p.get("quantity"),p.get("id"));
        }
        db.update("DELETE FROM cart WHERE user_id=?",user);audit(user,"CREATE_ORDER",id); return order(user,id);
    }
    @Transactional
    public Map<String,Object> pay(long user,String id) {
        var row=lockedOrder(user,id); String status=row.get("status").toString();
        if(status.equals("PAID")) return order(user,id);
        if(!status.equals("PENDING")) throw error(409,"当前订单不能支付");
        db.update("UPDATE orders SET status='PAID' WHERE id=?",id);audit(user,"DEMO_PAY",id);return order(user,id);
    }
    private Map<String,Object> lockedOrder(long user,String id) {
        var rows=db.queryForList("SELECT * FROM orders WHERE id=? AND user_id=? FOR UPDATE",id,user);
        if(rows.isEmpty()) throw error(404,"订单不存在");return rows.get(0);
    }
    @Transactional
    public Map<String,Object> cancel(long user,String id) {
        var row=lockedOrder(user,id); if(row.get("status").equals("CANCELLED")) return order(user,id);
        if(!row.get("status").equals("PENDING")) throw error(409,"只允许取消待付款订单");
        restoreStock(id);db.update("UPDATE orders SET status='CANCELLED' WHERE id=?",id);audit(user,"CANCEL_ORDER",id);return order(user,id);
    }
    @Transactional
    public Map<String,Object> refund(long user,String orderId,String reason,String key) {
        checkKey(key);reason=reason.strip();if(reason.length()<2 || reason.length()>500) throw error(400,"退款原因长度须为 2 到 500 字");
        var row=lockedOrder(user,orderId);
        var previous=db.queryForList("SELECT * FROM refunds WHERE order_id=?",orderId);
        if(!previous.isEmpty()) {
            if(previous.get(0).get("request_key").equals(key) && !previous.get(0).get("reason").equals(reason)) throw error(409,"同一请求标识不能用于不同退款原因");
            return previous.get(0);
        }
        if(!row.get("status").equals("PAID")) throw error(409,"当前仅支持未发货的已支付订单申请退款");
        String id="RF"+UUID.randomUUID().toString().replace("-","");
        db.update("INSERT INTO refunds(id,order_id,user_id,amount,reason,status,created_at,request_key) VALUES(?,?,?,?,?,?,?,?)",id,orderId,user,row.get("amount"),reason,"PENDING",System.currentTimeMillis(),key);
        audit(user,"REQUEST_REFUND",id);return db.queryForMap("SELECT * FROM refunds WHERE id=?",id);
    }
    public List<Map<String,Object>> refunds() { return db.queryForList("SELECT * FROM refunds ORDER BY created_at DESC"); }
    @Transactional
    public Map<String,Object> review(long admin,String id,boolean approve,String note) {
        var initial=db.queryForList("SELECT * FROM refunds WHERE id=?",id);if(initial.isEmpty())throw error(404,"退款申请不存在");
        String orderId=initial.get(0).get("order_id").toString();
        var order=db.queryForMap("SELECT * FROM orders WHERE id=? FOR UPDATE",orderId);
        var row=db.queryForMap("SELECT * FROM refunds WHERE id=? FOR UPDATE",id);
        String target=approve?"APPROVED":"REJECTED";
        if(row.get("status").equals(target))return row;
        if(!row.get("status").equals("PENDING")) throw error(409,"申请已处理");
        if(approve && !order.get("status").equals("PAID")) throw error(409,"订单状态已变化，不能退款");
        db.update("UPDATE refunds SET status=?,review_note=? WHERE id=?",target,note,id);
        if(approve) {restoreStock(orderId);db.update("UPDATE orders SET status='REFUNDED' WHERE id=?",orderId);}
        audit(admin,"REVIEW_REFUND_"+target,id);return db.queryForMap("SELECT * FROM refunds WHERE id=?",id);
    }
    public List<Map<String,Object>> adminOrders() { return db.queryForList("SELECT * FROM orders ORDER BY created_at DESC").stream().map(this::enrich).toList(); }
    @Transactional
    public void ship(long admin,String id) {
        var rows=db.queryForList("SELECT * FROM orders WHERE id=? FOR UPDATE",id); if(rows.isEmpty())throw error(404,"订单不存在");
        if(!rows.get(0).get("status").equals("PAID")) throw error(409,"订单不是待发货状态");
        if(db.queryForObject("SELECT COUNT(*) FROM refunds WHERE order_id=? AND status='PENDING'",Integer.class,id)>0)throw error(409,"请先处理待审核退款");
        db.update("UPDATE orders SET status='SHIPPED' WHERE id=?",id);audit(admin,"SHIP_ORDER",id);
    }
    @Transactional
    public void saveProduct(long admin,long id,String title,String category,String description,BigDecimal price,int stock,boolean active) {
        if(id<1 || price.signum()<0 || price.scale()>2 || price.compareTo(new BigDecimal("999999.99"))>0 || stock<0 || stock>1000000)throw error(400,"商品编号、价格或库存不合法");
        int count=db.update("UPDATE products SET title=?,category=?,description=?,price=?,stock=?,active=? WHERE id=?",title,category,description,price,stock,active,id);
        if(count==0)db.update("INSERT INTO products VALUES(?,?,?,?,?,?,?)",id,title,category,description,price,stock,active);
        audit(admin,"SAVE_PRODUCT",String.valueOf(id));
    }
    public Map<String,Object> logistics(long user,String id) {
        var o=order(user,id);boolean shipped=o.get("status").equals("SHIPPED");
        return Map.of("order_id",id,"status",o.get("status_desc"),"tracking_number",shipped?"DEMO-"+id:"","events",shipped?List.of("演示物流：商家已发货，等待揽收"):List.of("尚未发货"),"demo",true);
    }
    private void restoreStock(String id) { for(var p:db.queryForList("SELECT product_id,quantity FROM order_items WHERE order_id=? ORDER BY product_id",id))db.update("UPDATE products SET stock=stock+? WHERE id=?",p.get("quantity"),p.get("product_id")); }
    private void audit(long user,String action,String id) { db.update("INSERT INTO audit_log VALUES(?,?,?,?,?)",UUID.randomUUID().toString(),user,action,id,System.currentTimeMillis()); }
    private void checkKey(String key) { if(key==null || !key.matches("[A-Za-z0-9_-]{8,100}"))throw error(400,"需要有效的 Idempotency-Key"); }
}
