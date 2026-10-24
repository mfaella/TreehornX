// the new node is both the head and after the tail
struct Node {
    int data;
    struct Node *next;
};

void sll_unsafe_shape_push_front_and_back(struct Node *root) {
    struct Node *n;
    struct Node *last;
    struct Node *nxt;

    n = malloc(sizeof(struct Node));
    n->next = root;
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
    root = n;
}
