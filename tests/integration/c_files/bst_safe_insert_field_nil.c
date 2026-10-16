struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_safe_insert_field_nil(struct Node *root) {
    struct Node *curr;
    struct Node *n;
    int key;
    int value;
    int done;
    if (root != NULL) {
        curr = root;
        done = 0;
        while (done == 0) {
            value = curr->data;
            if (key < value) {
                if (curr->left == NULL) {
                    n = malloc(sizeof(struct Node));
                    n->data = key;
                    curr->left = n;
                    done = 1;
                } else {
                    curr = curr->left;
                }
            } else {
                if (curr->right == NULL) {
                    n = malloc(sizeof(struct Node));
                    n->data = key;
                    curr->right = n;
                    done = 1;
                } else {
                    curr = curr->right;
                }
            }
        }
    }
}
