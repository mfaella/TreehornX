// cycle when the left child equals the root: possible in a bst, impossible in a strict bst
struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_pre_shape_left_equal(struct Node *root) {
    int a;
    int b;
    struct Node *l;

    if (!root) {
        return;
    }
    l = root->left;
    if (!l) {
        return;
    }
    a = l->data;
    b = root->data;
    if (a == b) {
        l->left = root;
    }
}
