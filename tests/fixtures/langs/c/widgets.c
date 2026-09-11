/* Größe — 寸法 📦: 2-, 3- and 4-byte UTF-8 before every node, so a byte offset
   used on decoded text would shift every name, line and doc below this point. */
static const char *LABEL = "寸法 📦 größe";

/* Store one widget — größe 寸法 📦. */
int widget_store_save(int item) {
    return item;
}

/* Größe of the store — 寸法. */
int größe(void) {
    return 0;
}

/* Place one widget through the store. */
int widget_service_place(int item) {
    return widget_store_save(item);
}

/* Hand-counted: complexity 6 (1 + for, if, &&, if, else if), depth 2, 2 params. */
const char *grade(int score, const int *bonus) {
    int total = score;
    for (int i = 0; i < 3; i++) {
        if (bonus[i] > 0 && total < 100) {
            total += bonus[i];
        }
    }
    if (total > 90) {
        return "A";
    } else if (total > 50) {
        return "B";
    }
    return "C";
}
