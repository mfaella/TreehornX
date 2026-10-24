// the second node points back to the head when it is smaller: impossible in a sorted list
struct Node {
    int data;
    struct Node *next;
};

void sll_pre_shape_back_edge_if_unsorted(struct Node *root) {
    int x;
    int y;
    struct Node *a;

    if (!root) {
        return;
    }
    a = root->next;
    if (!a) {
        return;
    }
    x = root->data;
    y = a->data;
    if (y < x) {
        a->next = root;
    }
}
