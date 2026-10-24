// a new node between the root and its left child
struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_safe_shape_push_down_left(struct Node *root) {
    struct Node *l;
    struct Node *n;

    if (!root) {
        return;
    }
    l = root->left;
    n = malloc(sizeof(struct Node));
    root->left = n;
    n->left = l;
}
