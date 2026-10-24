// inserts a new node after the head
struct Node {
    int data;
    struct Node *next;
};

void sll_safe_shape_insert_second(struct Node *root) {
    struct Node *n;
    struct Node *b;

    if (!root) {
        return;
    }
    n = malloc(sizeof(struct Node));
    b = root->next;
    n->next = b;
    root->next = n;
}
