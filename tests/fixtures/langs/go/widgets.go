package widgets

import "net/http"

// WidgetStore persists widgets.
type WidgetStore struct {
	rows map[string]string
}

// Save stores one widget.
func (s *WidgetStore) Save(id string) string {
	return s.rows[id]
}

// WidgetService applies widget rules, then persists.
type WidgetService struct {
	store *WidgetStore
}

// Place places one widget through the store.
func (s *WidgetService) Place(id string) string {
	return s.store.Save(id)
}

// NewRouter wires the widget routes.
func NewRouter() *http.ServeMux {
	mux := http.NewServeMux()
	mux.HandleFunc("POST /widgets", handleCreateWidget)
	return mux
}

// handleCreateWidget is the POST /widgets handler.
func handleCreateWidget(w http.ResponseWriter, r *http.Request) {
	service := WidgetService{}
	service.Place(r.URL.Path)
}
