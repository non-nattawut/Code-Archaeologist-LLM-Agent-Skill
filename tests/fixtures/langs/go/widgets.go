package widgets

import "net/http"

// Größe — 寸法 📦: 2-, 3- and 4-byte UTF-8 before every node, so a byte offset
// used on decoded text would shift every name, line and doc below this point.
const label = "寸法 📦 größe"

// WidgetStore persists widgets.
type WidgetStore struct {
	rows map[string]string
}

// Save stores one widget — größe 寸法 📦.
func (s *WidgetStore) Save(id string) string {
	return s.rows[id]
}

// Größe of the store — 寸法.
func (s *WidgetStore) Größe() int {
	return 0
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
