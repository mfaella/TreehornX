// frees the leftmost node keeping the link to it
struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_unsafe_shape_remove_min_keep(struct Node *root) {
    struct Node *parent;
    struct Node *cur;
    struct Node *nxt;

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
    if (parent) {
        parent->left = cur;
        free(cur);
    }
}
