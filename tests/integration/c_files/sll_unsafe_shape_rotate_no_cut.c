// moves the head to the tail without cutting its next
struct Node {
    int data;
    struct Node *next;
};

void sll_unsafe_shape_rotate_no_cut(struct Node *root) {
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
    root = b;
}
