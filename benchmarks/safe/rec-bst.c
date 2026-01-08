enum PC { RETURN_CALL, RIGHT_CALL };

struct Node {
    int key;
    enum PC pc;
    struct Node *left;
    struct Node *right;
    struct Node *parent;
};

void sum_keys(struct Node *root) {
    struct Node *curr;
    struct Node *parent;
    int sum;
    int key;
    enum PC pc;

    curr = root;
    sum = 0;

    if (curr) {
        START:
        if(curr) { //L5
            curr->parent = parent;
            key = curr->key;
            sum = sum + key;
            // sum_keys(curr->left);
            parent = curr;
            parent->pc = RIGHT_CALL;
            curr = curr->left;
            goto START;
            // sum_keys(curr->right);
            RIGHT_CALL_LABEL:
            parent = curr; //13
            parent->pc = RETURN_CALL;;
            curr = curr->right;
            goto START;
        }
        else {
            RETURN_CALL_LABEL:
            curr = parent; //17
            if(curr) {
                parent = curr->parent;
                pc = curr->pc;
                if(pc == RIGHT_CALL) {
                    goto RIGHT_CALL_LABEL;
                }
                else {
                    goto RETURN_CALL_LABEL;
                }
            }
        }
    }
}
