struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_safe_insert_load(struct Node *root) {
    struct Node *curr;
    struct Node *n;
    struct Node *l;
    struct Node *r;
    int key;
    int value;
    int done;
    if (root != NULL) {
        curr = root;
        done = 0;
        while (done == 0) {
            value = curr->data;
            if (key < value) {
                l = curr->left;
                if (l == NULL) {
                    n = malloc(sizeof(struct Node));
                    n->data = key;
                    curr->left = n;
                    done = 1;
                } else {
                    curr = curr->left;
                }
            } else {
                r = curr->right;
                if (r == NULL) {
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
