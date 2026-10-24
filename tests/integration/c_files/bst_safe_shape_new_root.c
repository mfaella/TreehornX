// a new root with the old one as left child
struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_safe_shape_new_root(struct Node *root) {
    struct Node *n;

    n = malloc(sizeof(struct Node));
    n->left = root;
    root = n;
}
