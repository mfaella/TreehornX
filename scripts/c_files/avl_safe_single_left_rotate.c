#include <stdbool.h>

enum PC {
    LEFT_CALL_PC,
    RIGHT_CALL_PC
};

enum BF {
    LOW_LEFT, NEUTRAL, LOW_RIGHT
};

struct Node {
    int data;
    enum BF bf;
    struct Node *left;
    struct Node *right;
};

void avl_safe_single_left_rotate(struct Node *root, int value) {
    struct Node *current;
    struct Node *tmp;
    struct Node *new_root;
    struct Node *orphan;
    struct Node *c;

    enum BF tmp_bf;
    int tmp_data;

    current = root;

    while (current) {

        tmp_bf = current->bf;
        if (tmp_bf == LOW_RIGHT) {
            tmp = current->right;
            if(tmp) {
                tmp_bf = tmp->bf;
                if(tmp_bf == NEUTRAL || tmp_bf == LOW_RIGHT) {
                    // new_root = a
                    // orpa
                    new_root = tmp;
                    orphan   = new_root->left;

                    new_root->left = current;
                    current->right    = orphan;

                    if(current == root) {
                        root = new_root;
                    }
                    return;
                }
            }
        }

        tmp_data = current->data;
        if (value < tmp_data) {
            current    = current->left;
        } else {
            current    = current->right;
        }
    }
}
