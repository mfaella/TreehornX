struct Node {
    int value;
    struct Node *left;
    struct Node *right;
};

void bst_safe_find(struct Node* root, int key) {
    struct Node* current;
    struct Node* result;
    struct Node *null;
    int value;
    current = root;

    while (current) {
        value = current->value;
        if (value == key) {
            result = current;
            current = null;
        } else if (key < value) {
            current = current->left;
        } else {
            current = current->right;
        }
    }
}
