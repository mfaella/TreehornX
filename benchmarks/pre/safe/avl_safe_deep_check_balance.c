struct Node {
    int data;
    struct Node *left;
    struct Node *right;
    int height;
};

void avl_safe_deep_check_balance(struct Node *root) {
    struct Node *current;
    struct Node *tmp;
    struct Node *null;
    int left_height;
    int right_height;
    int tmp_height;
    if (root) {
        tmp_height = 1 - 2;
        current = root;
        while(current) {
            tmp_height = tmp_height + 1;
            tmp = current->left;
            if (!tmp) {
                current = current->right;
            }
            else {
                left_height = tmp->height;
                tmp = current->right;
                if (!tmp) {
                    current = current->left;
                }
                else {
                    right_height = tmp->height;
                    if (left_height > right_height) {
                        current = current->left;
                    }
                    else {
                        current = current->right;
                    }
                }
            }
        }
        left_height = root->height;
        if (left_height != tmp_height) {
            right_height = null->height;
        }
    }
}
