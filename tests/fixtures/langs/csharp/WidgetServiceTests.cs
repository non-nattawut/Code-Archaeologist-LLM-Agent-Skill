namespace Sample.Widgets;

/// <summary>C# test fixture: proves is_test_file fires on [Fact].</summary>
public class WidgetServiceTests
{
    private readonly WidgetService _service = new WidgetService(new WidgetStore());

    [Fact]
    public void PlacesThroughTheStore()
    {
        _service.Place(new Widget());
    }
}
