// a new second node, also pointed to by the third
struct Node {
    int data;
    struct Node *next;
};

void sll_unsafe_shape_new_shared(struct Node *root) {
    struct Node *a;
    struct Node *n;

    if (!root) {
        return;
    }
    a = root->next;
    n = malloc(sizeof(struct Node));
    root->next = n;
    n->next = a;
    if (a) {
        a->next = n;
    }
}
