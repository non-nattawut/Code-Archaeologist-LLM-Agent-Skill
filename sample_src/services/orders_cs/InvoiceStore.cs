namespace Sample.Invoices;

using System.Collections.Generic;

/// <summary>Where invoices are kept. Stands in for a database.</summary>
public class InvoiceStore
{
    private readonly Dictionary<string, Invoice> _rows = new();

    /// <summary>Store one invoice against an order id.</summary>
    public Invoice Put(string id, int total)
    {
        var invoice = new Invoice(id, total);
        _rows[id] = invoice;
        return invoice;
    }

    /// <summary>Read one invoice by id.</summary>
    public Invoice Get(string id)
    {
        return _rows.TryGetValue(id, out var found) ? found : null;
    }
}
