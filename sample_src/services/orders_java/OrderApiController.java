package com.example.orders;

/** HTTP entry point for the Java side of the order domain. */
@RestController
@RequestMapping("/java/orders")
public class OrderApiController {

    private final OrderWorkflow workflow;

    public OrderApiController(OrderWorkflow workflow) {
        this.workflow = workflow;
    }

    /** Place a new order. */
    @PostMapping
    public Order create(@RequestBody OrderRequest request) {
        return this.workflow.place(request);
    }

    /** Fetch one order by id. */
    @GetMapping("/{id}")
    public Order findOne(String id) {
        return workflow.find(id);
    }
}
