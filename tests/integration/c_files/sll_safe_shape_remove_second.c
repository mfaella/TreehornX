// unlinks and frees the second node
struct Node {
    int data;
    struct Node *next;
};

void sll_safe_shape_remove_second(struct Node *root) {
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
    a->next = c;
    free(b);
}
