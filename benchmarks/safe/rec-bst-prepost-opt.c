#include <stdlib.h>
#include<stdbool.h>

enum ReturnPC {
    B2, B3, RET
};

struct Node {
	int value;
	struct Node* left;
	struct Node* right;
	struct Node* parent;
	int minl;
	int maxl;
	_Bool isbstl;
	int minr;
	int maxr;
    _Bool isbstr;
	enum ReturnPC retpc;
	int min;
	int max;
	_Bool isbst;
};

void isBST(struct Node* root) {
	struct Node* current;
	struct Node* tmp;
	int return_min;
	int return_max;
	_Bool return_isbst;
	int value_tmp;
	enum ReturnPC tmp_retpc;
	_Bool current_isbst;
	current = root;
	if(!root) {
		return_isbst = true;
        return_min = 0;
        return_max = 0;
	}
	else {
		root->parent = tmp; //tmp is null
		START:
		//begin <blocco1-new>
		current->isbst = true;
		//end <blocco1-new>
		current->retpc = B2;
		tmp = current->left; //scende a sinistra
		if(!tmp) {
    		return_isbst = true;
            return_min = 0;
            return_max = 0;
            goto MyReturn;
		}
		tmp = current; // rewind (sale nel padre)
		current = current->left; //scende a sinistra
		current->parent = tmp;
		goto START;

		B2:
		current->isbstl = return_isbst;
		current->minl = return_min;
        current->maxl = return_max;
		//begin <blocco2-new>
		tmp = current->left; // scende nel sinistro
		if(tmp) {
            current->min = return_min; //risale
            current_isbst = current->isbst;
            value_tmp = current->value;
            current->isbst = current_isbst && return_isbst && value_tmp >= return_max;
       	}
       	else {
            value_tmp = current->value; // risale
      		current->min = value_tmp;
       	}
       	//end <blocco2-new>
        current->retpc = B3;
        tmp = current->right; // scendo nel destro
        if(!tmp) {
      		return_isbst = true;
            return_min = 0;
            return_max = 0;
            goto MyReturn;
        }
        tmp = current; // risale
        current = current->right; // riscende nel destro
        current->parent = tmp;
        goto START;

        B3:
        current->isbstr = return_isbst;
        current->minr = return_min;
        current->maxr = return_max;
        //begin <blocco3-new>
        tmp = current->right; //scende nel destro
        if(tmp) {
            current->max = return_max; //risale
            current_isbst = current->isbst;
            value_tmp = current->value;
            current->isbst = current_isbst && return_isbst && value_tmp <= return_min;
       	}
       	else {
            value_tmp = current->value; //risale
      		current->max = value_tmp;;
       	}
       	return_isbst = current->isbst;
       	return_min = current->min;
       	return_max = current->max;
       	current->retpc = RET;
        goto MyReturn;

       	MyReturn:
        tmp_retpc = current->retpc;
        tmp = current->parent; // sale nel padre
       	if(!tmp && tmp_retpc == RET) return;
        if(tmp_retpc == B2) {
            goto B2;
        }
        else if(tmp_retpc == B3) {
            goto B3;
        }
        else if(tmp_retpc == RET) {
           	current = tmp;
            goto MyReturn;
        }
    }
}
