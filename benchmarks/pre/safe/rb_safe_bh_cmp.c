enum Color {
    RED, BLACK
};

struct Node {
    struct Node *left;
    struct Node *right;
    int data;
    enum Color color;
};

void rb_safe_bh_cmp(struct Node *root) {
    struct Node *current;
    struct Node *null;
    int left_bh;
    int right_bh;
    enum Color tmp_color;

    left_bh = 0;
    right_bh = 0;

    if (!root) {
        return;
    }

    current = root->left;
    while(current) {
        tmp_color = current->color;
        if(tmp_color == BLACK) {
            left_bh = left_bh + 1;
        }
        current = current->left;
    }

    current = root->right;
    while(current) {
        tmp_color = current->color;
        if(tmp_color == BLACK) {
            right_bh = right_bh + 1;
        }
        current = current->right;
    }

    if (left_bh != right_bh) {
        tmp_color = null->color;
    }


}
