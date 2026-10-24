// frees the second node without unlinking it
struct Node {
    int data;
    struct Node *next;
};

void sll_unsafe_shape_free_second_linked(struct Node *root) {
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
    free(b);
}
