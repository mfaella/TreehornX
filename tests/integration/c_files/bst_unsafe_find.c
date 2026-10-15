struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_unsafe_find(struct Node *root) {
    int key;
    struct Node *curr;
    int key_curr;
    curr = root;
    while(curr != NULL) {
        key_curr = curr->data;
        if (key_curr == key) {
            curr = NULL;
        }
        else if (key < key_curr) {
            curr = curr->left;
            curr = curr->left;
        }
        else {
            curr = curr->right;
        }
    }
}
