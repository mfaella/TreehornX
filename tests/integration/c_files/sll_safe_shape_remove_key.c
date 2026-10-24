// removes the first node with data == key
struct Node {
    int data;
    struct Node *next;
};

void sll_safe_shape_remove_key(struct Node *root) {
    int key;
    int d;
    struct Node *prev;
    struct Node *cur;
    struct Node *nxt;

    prev = NULL;
    cur = root;
    while (cur) {
        d = cur->data;
        if (d == key) {
            break;
        }
        prev = cur;
        cur = cur->next;
    }
    if (!cur) {
        return;
    }
    nxt = cur->next;
    if (prev) {
        prev->next = nxt;
    } else {
        root = nxt;
    }
    free(cur);
}
