package com.example.orders;

/** Application service: price an order, then archive it. */
@Service
public class OrderWorkflow {

    private final OrderArchive archive;
    private final PricingRule pricing;

    public OrderWorkflow(OrderArchive archive, PricingRule pricing) {
        this.archive = archive;
        this.pricing = pricing;
    }

    /** Price the order and store the result. */
    public Order place(OrderRequest request) {
        // `pricing` is an interface with two implementations, so which `price`
        // runs here is a runtime fact. The extractor drops this call rather than
        // picking one of them -- see PricingRule.java.
        int total = pricing.price(request);
        return archive.save(request, total);
    }

    /** Read one order back out of the archive. */
    public Order find(String id) {
        return archive.get(id);
    }
}
