struct Node {
    int value;
    struct Node *next;
};

void sll_unsafe_find(struct Node *root, int key) {
    struct Node *tmp;
    struct Node *x;
    struct Node *result_node;
    struct Node *null;
    int result;

    x = root;


    while(x) {
        result = x->value;
        if(result == key) {
            result_node = x;
            x = null;
        }
        else {
            x = x->next;
        }
    }

    result = x->value;
}
