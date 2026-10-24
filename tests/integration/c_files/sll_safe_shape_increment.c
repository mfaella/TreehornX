// increments every data field
struct Node {
    int data;
    struct Node *next;
};

void sll_safe_shape_increment(struct Node *root) {
    int d;
    struct Node *cur;

    cur = root;
    while (cur) {
        d = cur->data;
        d = d + 1;
        cur->data = d;
        cur = cur->next;
    }
}
