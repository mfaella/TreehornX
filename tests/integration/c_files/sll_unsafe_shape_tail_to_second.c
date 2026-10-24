// the tail points to the second node
struct Node {
    int data;
    struct Node *next;
};

void sll_unsafe_shape_tail_to_second(struct Node *root) {
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
    last->next = b;
}
