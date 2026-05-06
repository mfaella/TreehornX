enum Color {
    RED, BLACK
};

struct Node {
    struct Node *left;
    struct Node *right;
    int data;
    enum Color color;
};

void rb_safe_property_3(struct Node *root) {
    struct Node *current;
    struct Node *tmp;
    struct Node *null;
    int left_bh;
    int right_bh;
    enum Color tmp_color;
    enum Color current_color;

    left_bh = 0;
    right_bh = 0;

    if (!root) {
        return;
    }

    current = root;
    tmp = current->left;
    while(tmp) {
        current_color = current->color;
        tmp_color = tmp->color;
        if(current_color == RED && tmp_color == RED) {
            left_bh = null->data;
        }
        current = tmp;
        tmp = tmp->left;
    }


}
