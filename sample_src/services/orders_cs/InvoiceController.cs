namespace Sample.Invoices;

/// <summary>HTTP entry point for invoices.</summary>
[ApiController]
[Route("cs/[controller]")]
public class InvoiceController : ControllerBase
{
    private readonly InvoiceService _service;

    public InvoiceController(InvoiceService service)
    {
        _service = service;
    }

    /// <summary>Issue an invoice for one order.</summary>
    [HttpPost]
    public Invoice Create(InvoiceRequest request)
    {
        return _service.Issue(request);
    }

    /// <summary>Fetch one invoice by id.</summary>
    [HttpGet("{id}")]
    public Invoice Find(string id)
    {
        return _service.Find(id);
    }
}
