// a node points back to the head at the first descent: impossible in a sorted list
struct Node {
    int data;
    struct Node *next;
};

void sll_pre_shape_cycle_on_descent(struct Node *root) {
    int x;
    int y;
    struct Node *cur;
    struct Node *nxt;

    cur = root;
    while (cur) {
        nxt = cur->next;
        if (!nxt) {
            break;
        }
        x = cur->data;
        y = nxt->data;
        if (y < x) {
            nxt->next = root;
            break;
        }
        cur = nxt;
    }
}
