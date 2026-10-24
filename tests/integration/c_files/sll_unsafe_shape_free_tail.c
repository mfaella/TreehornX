// frees the tail without unlinking it
struct Node {
    int data;
    struct Node *next;
};

void sll_unsafe_shape_free_tail(struct Node *root) {
    struct Node *last;
    struct Node *nxt;

    if (!root) {
        return;
    }
    last = root;
    nxt = last->next;
    while (nxt) {
        last = nxt;
        nxt = last->next;
    }
    if (last != root) {
        free(last);
    }
}
