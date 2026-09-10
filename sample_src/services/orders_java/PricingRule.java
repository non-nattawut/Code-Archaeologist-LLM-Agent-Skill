package com.example.orders;

/** How an order's total is calculated. */
public interface PricingRule {

    /** What this order costs, in cents. */
    int price(OrderRequest request);
}

/** Everything costs the same. */
class FlatRate implements PricingRule {

    /** One price, whatever the order says. */
    public int price(OrderRequest request) {
        return 100;
    }
}

/** Bulk orders get a discount. */
class TieredRate implements PricingRule {

    /** Cheaper per unit above ten units. */
    public int price(OrderRequest request) {
        return request.units() > 10 ? 80 : 100;
    }
}
