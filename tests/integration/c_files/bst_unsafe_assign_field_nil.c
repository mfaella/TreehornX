struct Node { int data; struct Node *left; struct Node *right; };
void bst_unsafe_assign_field_nil(struct Node *root) {
    struct Node *x;
    _Bool b;
    int d;
    if (root != NULL) {
        b = root->left == NULL;
        if (b) { x = root->left; d = x->data; }
    }
}
