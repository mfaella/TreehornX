// the second node points back to the head
struct Node {
    int data;
    struct Node *next;
};

void sll_unsafe_shape_back_edge(struct Node *root) {
    struct Node *a;
    struct Node *b;

    a = root;
    if (!a) {
        return;
    }
    b = a->next;
    if (!b) {
        return;
    }
    b->next = a;
}
