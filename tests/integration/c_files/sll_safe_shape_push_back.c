// appends a new node
struct Node {
    int data;
    struct Node *next;
};

void sll_safe_shape_push_back(struct Node *root) {
    struct Node *n;
    struct Node *last;
    struct Node *nxt;

    n = malloc(sizeof(struct Node));
    if (!root) {
        root = n;
        return;
    }
    last = root;
    nxt = last->next;
    while (nxt) {
        last = nxt;
        nxt = last->next;
    }
    last->next = n;
}
