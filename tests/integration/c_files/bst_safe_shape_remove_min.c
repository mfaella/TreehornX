// removes the leftmost node, its right subtree takes its place
struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_safe_shape_remove_min(struct Node *root) {
    struct Node *parent;
    struct Node *cur;
    struct Node *nxt;
    struct Node *r;

    if (!root) {
        return;
    }
    parent = NULL;
    cur = root;
    nxt = cur->left;
    while (nxt) {
        parent = cur;
        cur = nxt;
        nxt = cur->left;
    }
    r = cur->right;
    if (parent) {
        parent->left = r;
    } else {
        root = r;
    }
    free(cur);
}
