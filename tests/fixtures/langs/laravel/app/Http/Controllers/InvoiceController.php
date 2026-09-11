<?php

/** Invoices, routed by `Route::resource('invoices', ...)->only(['index', 'show'])`. */
class InvoiceController
{
    /** List invoices. */
    public function index()
    {
        return [];
    }

    /** Show one invoice. */
    public function show($invoice)
    {
        return $invoice;
    }
}
