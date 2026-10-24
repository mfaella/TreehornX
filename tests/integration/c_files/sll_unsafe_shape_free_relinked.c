// skips the second node, then frees the third instead of the second
struct Node {
    int data;
    struct Node *next;
};

void sll_unsafe_shape_free_relinked(struct Node *root) {
    struct Node *a;
    struct Node *b;
    struct Node *c;

    a = root;
    if (!a) {
        return;
    }
    b = a->next;
    if (!b) {
        return;
    }
    c = b->next;
    if (!c) {
        return;
    }
    a->next = c;
    free(c);
}
