struct Node {
    int data;
    struct Node *left;
    struct Node *right;
    int height;
};

void avl_safe_check_balance_and_root_height(struct Node *root) {
    struct Node *tmp;
    struct Node *null;
    int left_height;
    int right_height;
    int tmp_value;
    int root_data;
    if (root) {
        tmp = root->left;
        if (tmp) {
            left_height = tmp->height;
        }
        else {
            left_height = 0;
        }
        tmp = root->right;
        if (tmp) {
            right_height = tmp->height;
        }
        else {
            right_height = 0;
        }
        tmp_value = left_height - right_height;
        if (tmp_value < 0) {
            tmp_value = right_height - left_height;
        }
        if(tmp_value > 1) {
            tmp_value = null->data; //error
        }
        if (left_height < right_height) {
            tmp_value = right_height;
        }
        else {
            tmp_value = left_height;
        }
        root_data = root->height;
        if(root_data != tmp_value + 1) {
            tmp_value = null->data; //error
        }
    }
}
