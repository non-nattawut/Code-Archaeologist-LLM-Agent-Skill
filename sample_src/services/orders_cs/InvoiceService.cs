namespace Sample.Invoices;

/// <summary>Invoice rules: work out the total, then store it.</summary>
public class InvoiceService
{
    private readonly InvoiceStore _store;

    public InvoiceService(InvoiceStore store)
    {
        _store = store;
    }

    /// <summary>Issue an invoice and store it.</summary>
    public Invoice Issue(InvoiceRequest request)
    {
        var total = Total(request);
        return _store.Put(request.Id, total);
    }

    /// <summary>Read one invoice back.</summary>
    public Invoice Find(string id)
    {
        return _store.Get(id);
    }

    /// <summary>Total for a whole request.</summary>
    public int Total(InvoiceRequest request)
    {
        return Total(request.Units, request.UnitPrice);
    }

    /// <summary>Total for a quantity at a price. This is an overload: both
    /// signatures share one node id, which is one of the reasons this tier is
    /// marked approximate.</summary>
    public int Total(int units, int unitPrice)
    {
        return units * unitPrice;
    }
}
