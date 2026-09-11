// Größe — 寸法 📦: 2-, 3- and 4-byte UTF-8 before every node, so a byte offset
// used on decoded text would shift every name, line and doc below this point.
const LABEL: &str = "寸法 📦 größe";

/// Persists widgets.
pub struct WidgetStore {
    rows: Vec<String>,
}

impl WidgetStore {
    /// Store one widget — größe 寸法 📦.
    pub fn save(&self, item: String) -> String {
        item
    }

    /// Größe of the store — 寸法.
    pub fn größe(&self) -> i32 {
        0
    }
}

/// Applies widget rules, then persists.
pub struct WidgetService {
    store: WidgetStore,
}

impl WidgetService {
    /// Place one widget through the store.
    pub fn place(&self, item: String) -> String {
        self.store.save(item)
    }

    /// Hand-counted: complexity 6 (1 + for, if, &&, if, else if), depth 2, 2 params.
    pub fn grade(score: i32, bonus: &[i32]) -> &'static str {
        let mut total = score;
        for b in bonus {
            if *b > 0 && total < 100 {
                total += b;
            }
        }
        if total > 90 {
            "A"
        } else if total > 50 {
            "B"
        } else {
            "C"
        }
    }
}

/// POST /widgets.
#[post("/widgets")]
async fn create_widget(service: WidgetService, item: String) -> String {
    service.place(item)
}
