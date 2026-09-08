package com.example.orders;

import java.util.HashMap;
import java.util.Map;

/** Where Java orders are kept. Stands in for a JPA repository. */
@Repository
public class OrderArchive {

    private final Map<String, Order> rows = new HashMap<>();

    /** Store one order and return it. */
    public Order save(OrderRequest request, int total) {
        Order order = new Order(request.id(), total);
        rows.put(order.id(), order);
        return order;
    }

    /** Look up one order by id. */
    public Order get(String id) {
        return rows.get(id);
    }
}
