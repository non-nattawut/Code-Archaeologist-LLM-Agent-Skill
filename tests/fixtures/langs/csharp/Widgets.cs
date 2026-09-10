namespace Sample.Widgets;

/// <summary>Persists widgets.</summary>
public class WidgetStore
{
    /// <summary>Store one widget.</summary>
    public Widget Save(Widget item)
    {
        return item;
    }
}

/// <summary>Applies widget rules, then persists.</summary>
public class WidgetService
{
    private readonly WidgetStore _store;

    public WidgetService(WidgetStore store)
    {
        _store = store;
    }

    /// <summary>Place one widget through the store.</summary>
    public Widget Place(Widget item)
    {
        return _store.Save(item);
    }
}

/// <summary>HTTP entry point for widgets.</summary>
[ApiController]
[Route("widgets")]
public class WidgetController : ControllerBase
{
    private readonly WidgetService _service;

    public WidgetController(WidgetService service)
    {
        _service = service;
    }

    /// <summary>POST /widgets.</summary>
    [HttpPost]
    public Widget Create(Widget item)
    {
        return _service.Place(item);
    }
}
