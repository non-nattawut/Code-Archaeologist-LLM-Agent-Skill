package widgets

import "testing"

// TestPlace proves is_test_file fires on the _test.go convention.
func TestPlace(t *testing.T) {
	service := WidgetService{}
	service.Place("w-1")
}
