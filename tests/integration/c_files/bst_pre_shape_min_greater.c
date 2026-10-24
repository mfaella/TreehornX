// cycle when the leftmost node is greater than the root: impossible in a bst
struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_pre_shape_min_greater(struct Node *root) {
    int a;
    int b;
    struct Node *cur;
    struct Node *nxt;

    if (!root) {
        return;
    }
    cur = root;
    nxt = cur->left;
    while (nxt) {
        cur = nxt;
        nxt = cur->left;
    }
    a = cur->data;
    b = root->data;
    if (a > b) {
        cur->left = root;
    }
}
