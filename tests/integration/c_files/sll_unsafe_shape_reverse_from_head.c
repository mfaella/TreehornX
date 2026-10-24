// complete reverse starting with y = root: the old head keeps its next
struct Node {
    int data;
    struct Node *next;
};

void sll_unsafe_shape_reverse_from_head(struct Node *root) {
    struct Node *y;
    struct Node *tmp;
    struct Node *first;

    if (!root) {
        return;
    }
    y = root;
    first = root->next;
    while (first) {
        tmp = first->next;
        first->next = y;
        y = first;
        first = tmp;
    }
    root = y;
}
