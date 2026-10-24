// inserts a new head
struct Node {
    int data;
    struct Node *next;
};

void sll_safe_shape_push_front(struct Node *root) {
    struct Node *n;

    n = malloc(sizeof(struct Node));
    n->next = root;
    root = n;
}
