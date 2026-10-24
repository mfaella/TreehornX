// moves the head to the tail
struct Node {
    int data;
    struct Node *next;
};

void sll_safe_shape_rotate(struct Node *root) {
    struct Node *a;
    struct Node *b;
    struct Node *last;
    struct Node *nxt;

    a = root;
    if (!a) {
        return;
    }
    b = a->next;
    if (!b) {
        return;
    }
    last = b;
    nxt = last->next;
    while (nxt) {
        last = nxt;
        nxt = last->next;
    }
    last->next = a;
    a->next = NULL;
    root = b;
}
