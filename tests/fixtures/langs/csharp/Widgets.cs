namespace Sample.Widgets;

// Größe — 寸法 📦: 2-, 3- and 4-byte UTF-8 before every node, so a byte offset
// used on decoded text would shift every name, line and doc below this point.

/// <summary>Persists widgets.</summary>
public class WidgetStore
{
    public const string Label = "寸法 📦 größe";

    /// <summary>Store one widget — größe 寸法 📦.</summary>
    public Widget Save(Widget item)
    {
        return item;
    }

    /// <summary>Größe of the store — 寸法.</summary>
    public int Größe()
    {
        return 0;
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
